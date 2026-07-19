from dataclasses import dataclass
from decimal import Decimal
import logging
import math
import re
from typing import List, Optional

from rapidfuzz import fuzz

from database.db_manager import DatabaseManager
from models.entites import SectionProjet
from repositories.correspondance_dpgf_repository import CorrespondanceDpgfRepository
from repositories.parametre_repository import ParametreRepository
from repositories.section_projet_repository import SectionProjetRepository
from services.import_bibliotheque_service import ImportBibliothequeService
from services.parametre_service import ParametreService

logger = logging.getLogger(__name__)

STOPWORDS_FR = {
    "de", "du", "des", "le", "la", "les", "un", "une", "et", "ou",
    "pour", "avec", "sur", "sous", "dans", "en", "a", "au", "aux",
    "par", "ce", "cette", "ces",
}

TOKEN_SET_WEIGHT = 0.5
PARTIAL_WEIGHT = 0.3
TOKEN_SORT_WEIGHT = 0.2

UNIT_MATCH_BONUS = 10
UNIT_MISMATCH_PENALTY = 8
FAMILY_MATCH_BONUS = 8
NO_COMMON_TECHNICAL_WORD_PENALTY = 18
DIMENSION_EXACT_BONUS = 20
DIMENSION_MISMATCH_PENALTY = 8
DEFAULT_AI_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_AI_SEMANTIC_WEIGHT = Decimal("0.65")
DEFAULT_AI_TEXT_WEIGHT = Decimal("0.35")


@dataclass
class MatchingResult:
    ouvrage_bibliotheque_id: int
    score: Decimal
    code: str
    designation: str
    famille: str
    unite: str
    debourse_sec_import: Optional[Decimal]
    pv_eg_ht_import: Optional[Decimal]
    bibliotheque_nom: str
    corps_metier: str


@dataclass
class RapprochementProgress:
    total: int
    traites: int = 0
    propositions: int = 0
    candidats_avant_filtre: int = 0
    candidats_apres_metier: int = 0
    candidats_scores: int = 0
    annule: bool = False


@dataclass
class RechercheIaProgress:
    total: int
    traites: int = 0
    propositions: int = 0
    candidats_scores: int = 0
    annule: bool = False


class CorrespondanceService:
    def __init__(
        self,
        db_manager: DatabaseManager,
        correspondance_repo: CorrespondanceDpgfRepository,
        section_repo: SectionProjetRepository,
        parametre_service: ParametreService,
    ):
        self.db = db_manager
        self.correspondance_repo = correspondance_repo
        self.section_repo = section_repo
        self.parametre_service = parametre_service
        self._slugger = ImportBibliothequeService.__new__(ImportBibliothequeService)
        self._sections_cache_by_projet = {}
        self._embedding_model = None

    def rechercher(self, ouvrage_projet_id: int, elargir_toutes_bibliotheques: bool = False, enregistrer: bool = True) -> List[MatchingResult]:
        section = self._get_section(ouvrage_projet_id)
        if not section:
            return []

        score_minimum = self.score_minimum()
        candidates = self._catalogue_candidates()
        candidates_before_filter = candidates
        active_project_libraries = self._active_project_libraries_count(section.projet_id)
        active_global_libraries = len({candidate["bibliotheque_id"] for candidate in candidates_before_filter})
        logger.info(
            "Matching DPGF: RapidFuzz=%s, seuil=%s, ouvrage_projet_id=%s, elargi=%s",
            "0.5*token_set_ratio + 0.3*partial_ratio + 0.2*token_sort_ratio",
            score_minimum,
            ouvrage_projet_id,
            elargir_toutes_bibliotheques,
        )
        logger.info(
            "Matching DPGF: texte DPGF brut=%r normalise=%r",
            section.libelle,
            self._search_text(section.libelle),
        )
        logger.info(
            "Matching DPGF: bibliotheques_projet actives projet_id=%s count=%s; bibliotheques actives globales count=%s; ouvrages candidats avant filtre corps_metier=%s",
            section.projet_id,
            active_project_libraries if active_project_libraries is not None else "table_absente",
            active_global_libraries,
            len(candidates_before_filter),
        )
        if not elargir_toutes_bibliotheques:
            lot_label = self._top_parent_label(section)
            lot_source = section.feuille_source or ""
            compared_corps_metier = sorted({candidate["corps_metier"] or "" for candidate in candidates_before_filter})
            candidates = self._filter_candidates_by_metier(section, candidates)
            logger.info(
                "Matching DPGF: filtre corps_metier applique; candidats apres filtre=%s; corps_metier compares=%r; nom_lot=%r; feuille_source=%r",
                len(candidates),
                compared_corps_metier,
                lot_label,
                lot_source,
            )
        else:
            logger.info(
                "Matching DPGF: filtre corps_metier non applique; candidats scores=%s",
                len(candidates),
            )

        candidates = self._prefilter_candidates_by_keywords(section, candidates)
        results, diagnostic = self._score_candidates(section, candidates, score_minimum)

        diagnostic.sort(key=lambda item: item[0], reverse=True)
        logger.info(
            "Matching DPGF: candidats effectivement scores=%s; top3_scores=%s",
            len(diagnostic),
            [
                {
                    "score": round(score, 2),
                    "code": candidate["code"],
                    "designation": candidate["designation"],
                    "bibliotheque": candidate["bibliotheque_nom"],
                    "corps_metier": candidate["corps_metier"],
                }
                for score, candidate, _details in diagnostic[:3]
            ],
        )
        for rank, (score, candidate, details) in enumerate(diagnostic[:10], start=1):
            logger.info(
                "Matching DPGF: candidat #%s score=%.2f code=%r designation=%r famille=%r biblio=%r normalise=%r details=%s",
                rank,
                score,
                candidate["code"],
                candidate["designation"],
                candidate["famille"],
                candidate["bibliotheque_nom"],
                details["biblio_text"],
                details,
            )

        results.sort(key=lambda item: item.score, reverse=True)
        results = results[:10]
        if enregistrer:
            for result in results:
                self.correspondance_repo.upsert_proposition(
                    ouvrage_projet_id,
                    result.ouvrage_bibliotheque_id,
                    result.score,
                    "automatique",
                )
        return results

    def rechercher_ia(
        self,
        ouvrage_projet_id: int,
        rechercher_toutes_bibliotheques: bool = False,
        enregistrer: bool = True,
        model=None,
    ) -> List[MatchingResult]:
        section = self._get_section(ouvrage_projet_id)
        if not section:
            return []
        candidates = self._candidates_for_ai_section(section, rechercher_toutes_bibliotheques)
        if not candidates:
            return []
        results = self._score_candidates_ia(section, candidates, self.score_minimum(), model=model)
        if enregistrer:
            for result in results:
                self.correspondance_repo.upsert_proposition(
                    ouvrage_projet_id,
                    result.ouvrage_bibliotheque_id,
                    result.score,
                    "ia",
                )
        return results

    def lancer_recherche_ia_projet(
        self,
        projet_id: int,
        rechercher_toutes_bibliotheques: bool = False,
        bibliotheque_id: Optional[int] = None,
        progress_callback=None,
        should_cancel=None,
        model=None,
    ) -> RechercheIaProgress:
        sections = self.sections_a_matcher(projet_id)
        progress = RechercheIaProgress(total=len(sections))
        if not sections:
            if progress_callback:
                progress_callback(progress)
            return progress

        embedding_model = model or self._get_embedding_model()
        score_minimum = self.score_minimum()
        candidates_all = self._catalogue_candidates()
        if bibliotheque_id is not None:
            candidates_all = [
                candidate for candidate in candidates_all
                if candidate["bibliotheque_id"] == bibliotheque_id
            ]
        candidate_texts = [
            f"{candidate['designation'] or ''} {candidate['famille'] or ''}".strip()
            for candidate in candidates_all
        ]
        logger.info(
            "Matching IA: encodage candidats projet_id=%s candidats=%s toutes_bibliotheques=%s",
            projet_id,
            len(candidates_all),
            rechercher_toutes_bibliotheques,
        )
        candidate_embeddings = embedding_model.encode(candidate_texts) if candidate_texts else []
        candidates_with_embeddings = list(zip(candidates_all, candidate_embeddings))
        if bibliotheque_id is not None:
            active_project_ids = {bibliotheque_id}
            rechercher_toutes_bibliotheques = False
        else:
            active_project_ids = None if rechercher_toutes_bibliotheques else self._active_project_library_ids(projet_id)
        with self.db.get_connection() as conn:
            try:
                for section in sections:
                    if should_cancel and should_cancel():
                        progress.annule = True
                        break
                    scoped = self._filter_ai_candidates_with_embeddings(
                        section,
                        candidates_with_embeddings,
                        rechercher_toutes_bibliotheques,
                        active_project_ids,
                    )
                    progress.candidats_scores += len(scoped)
                    results = self._score_candidates_ia_with_embeddings(section, scoped, score_minimum, embedding_model)
                    for result in results:
                        self.correspondance_repo.upsert_proposition_conn(
                            conn,
                            section.id,
                            result.ouvrage_bibliotheque_id,
                            result.score,
                            "ia",
                        )
                        progress.propositions += 1
                    progress.traites += 1
                    if progress_callback:
                        progress_callback(progress)
                if progress.annule:
                    conn.rollback()
                else:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
        return progress

    def recherche_catalogue_libre(self, terme: str = "", famille: str = "", code: str = "") -> List[dict]:
        terme_slug = self._slug(terme)
        famille_slug = self._slug(famille)
        code_slug = self._slug(code)
        results = []
        for candidate in self._catalogue_candidates():
            if code_slug and code_slug not in self._slug(candidate["code"]):
                continue
            if famille_slug and famille_slug not in self._slug(candidate["famille"]):
                continue
            searchable = self._slug(f"{candidate['code']} {candidate['designation']} {candidate['famille']}")
            if terme_slug and terme_slug not in searchable:
                continue
            results.append(candidate)
        return results

    def associer_resultat(self, correspondance_id: int):
        self.correspondance_repo.valider(correspondance_id)

    def associer_resultat_pour_ouvrage(self, ouvrage_projet_id: int, correspondance_id: int):
        self.correspondance_repo.valider_pour_ouvrage(ouvrage_projet_id, correspondance_id)

    def associer_plusieurs(self, correspondance_ids: List[int]):
        self.correspondance_repo.valider_plusieurs(correspondance_ids)

    def associer_selection(self, selections: dict[int, int]):
        self.correspondance_repo.valider_selection(selections)

    def lancer_rapprochement_projet(
        self,
        projet_id: int,
        elargir_toutes_bibliotheques: bool = False,
        batch_size: int = 200,
        progress_callback=None,
        should_cancel=None,
    ) -> RapprochementProgress:
        sections = self.sections_a_matcher(projet_id)
        progress = RapprochementProgress(total=len(sections))
        if not sections:
            if progress_callback:
                progress_callback(progress)
            return progress

        score_minimum = self.score_minimum()
        candidates_all = self._catalogue_candidates()
        progress.candidats_avant_filtre = len(candidates_all)
        candidate_index = self._build_candidate_keyword_index(candidates_all)

        pending = []
        with self.db.get_connection() as conn:
            try:
                for section in sections:
                    if should_cancel and should_cancel():
                        progress.annule = True
                        break

                    candidates = candidates_all
                    if not elargir_toutes_bibliotheques:
                        candidates = self._filter_candidates_by_metier(section, candidates)
                    progress.candidats_apres_metier += len(candidates)
                    candidates = self._prefilter_candidates_by_keywords(section, candidates, candidate_index)
                    progress.candidats_scores += len(candidates)
                    results, _diagnostic = self._score_candidates(section, candidates, score_minimum)
                    for result in results[:10]:
                        pending.append((section.id, result))

                    progress.traites += 1
                    if progress.traites % batch_size == 0:
                        progress.propositions += self._commit_pending(conn, pending)
                        pending.clear()
                        conn.commit()
                        logger.info(
                            "Rapprochement DPGF: commit lot traite=%s/%s propositions=%s",
                            progress.traites,
                            progress.total,
                            progress.propositions,
                        )
                    if progress_callback:
                        progress_callback(progress)

                if pending and not progress.annule:
                    progress.propositions += self._commit_pending(conn, pending)
                    pending.clear()
                if progress.annule:
                    conn.rollback()
                    logger.info("Rapprochement DPGF: annulation demandee apres %s/%s lignes.", progress.traites, progress.total)
                else:
                    conn.commit()
                    logger.info("Rapprochement DPGF: commit final traite=%s propositions=%s", progress.traites, progress.propositions)
            except Exception:
                conn.rollback()
                raise
        return progress

    def sections_a_matcher(self, projet_id: int) -> List[SectionProjet]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*
                FROM sections_projet s
                WHERE s.projet_id = ?
                  AND s.type_ligne IN ('ouvrage', 'pour_memoire')
                  AND TRIM(COALESCE(s.libelle, '')) <> ''
                  AND NOT EXISTS (
                      SELECT 1 FROM sections_projet child WHERE child.parent_id = s.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM correspondances_dpgf c
                      WHERE c.ouvrage_projet_id = s.id AND c.statut = 'validee'
                  )
                ORDER BY s.ordre_affichage, s.id
                """,
                (projet_id,),
            ).fetchall()
            sections = [self.section_repo._row_to_section(row) for row in rows]
        return [section for section in sections if self._search_text(section.libelle)]

    def estimer_rapprochement(self, projet_id: int, elargir_toutes_bibliotheques: bool = False) -> dict:
        sections = self.sections_a_matcher(projet_id)
        candidates_all = self._catalogue_candidates()
        index = self._build_candidate_keyword_index(candidates_all)
        estimated = 0
        sampled = sections[: min(20, len(sections))]
        if sampled:
            for section in sampled:
                candidates = candidates_all if elargir_toutes_bibliotheques else [
                    candidate for candidate in self._filter_candidates_by_metier(section, candidates_all)
                ]
                estimated += len(self._prefilter_candidates_by_keywords(section, candidates, index))
            estimated = int((estimated / len(sampled)) * len(sections))
        return {
            "lignes": len(sections),
            "candidats": len(candidates_all),
            "comparaisons_estimees": estimated,
        }

    def associer_manuellement(self, ouvrage_projet_id: int, ouvrage_bibliotheque_id: int):
        return self.correspondance_repo.creer_manuelle_validee(ouvrage_projet_id, ouvrage_bibliotheque_id)

    def supprimer_association(self, correspondance_id: int):
        self.correspondance_repo.supprimer(correspondance_id)

    def supprimer_correspondances_ouvrage(self, ouvrage_projet_id: int):
        self.correspondance_repo.supprimer_pour_ouvrage(ouvrage_projet_id)

    def annuler_validation_ouvrage(self, ouvrage_projet_id: int):
        self.correspondance_repo.annuler_validation_pour_ouvrage(ouvrage_projet_id)

    def correspondances_pour_ouvrage(self, ouvrage_projet_id: int) -> List[dict]:
        return self.correspondance_repo.get_enriched_by_ouvrage_projet(ouvrage_projet_id)

    def statut_ouvrage(self, ouvrage_projet_id: int) -> str:
        correspondances = self.correspondance_repo.get_by_ouvrage_projet(ouvrage_projet_id)
        if any(c.statut == "validee" for c in correspondances):
            return "Validée"
        if any(c.statut == "proposee" for c in correspondances):
            return "Proposée"
        return "Aucune"

    def score_minimum(self) -> Decimal:
        param = self.parametre_service.obtenir_parametre("score_minimum_matching")
        if not param:
            self.parametre_service.creer_ou_modifier_parametre(
                "score_minimum_matching",
                "60",
                "decimal",
                "score",
                "Score minimum pour proposer une correspondance DPGF-bibliothèque",
            )
            return Decimal("60")
        return Decimal(str(param.valeur))

    def poids_matching_ia(self) -> tuple[Decimal, Decimal]:
        semantic = self._decimal_param(
            "poids_matching_ia_semantique",
            DEFAULT_AI_SEMANTIC_WEIGHT,
            "Poids du score sémantique IA dans le matching hybride",
        )
        textual = self._decimal_param(
            "poids_matching_ia_textuel",
            DEFAULT_AI_TEXT_WEIGHT,
            "Poids du score textuel RapidFuzz dans le matching hybride IA",
        )
        total = semantic + textual
        if total <= 0:
            return DEFAULT_AI_SEMANTIC_WEIGHT, DEFAULT_AI_TEXT_WEIGHT
        return semantic / total, textual / total

    def normaliser_unite(self, unite: Optional[str]) -> str:
        raw = (unite or "").strip().lower().replace("²", "2")
        text = self._slug(raw)
        if text in {"m2"}:
            return "m2"
        if text in {"ml", "metre_lineaire", "metres_lineaires", "metrelineaire", "metreslineaires"}:
            return "ml"
        if text in {"u", "unite", "unites"}:
            return "u"
        if text in {"ens", "ensemble"}:
            return "ens"
        return text

    def _score(self, section: SectionProjet, candidate: dict) -> float:
        return self._score_details(section, candidate)[0]

    def _score_candidates(self, section: SectionProjet, candidates: List[dict], score_minimum: Decimal) -> tuple[List[MatchingResult], list]:
        results = []
        diagnostic = []
        for candidate in candidates:
            score, details = self._score_details(section, candidate)
            diagnostic.append((score, candidate, details))
            if score >= score_minimum:
                results.append(self._to_result(candidate, Decimal(str(round(score, 2)))))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:10], diagnostic

    def _score_candidates_ia(self, section: SectionProjet, candidates: List[dict], score_minimum: Decimal, model=None) -> List[MatchingResult]:
        if not candidates:
            return []
        embedding_model = model or self._get_embedding_model()
        dpgf_text = section.libelle or ""
        candidate_texts = [f"{candidate['designation'] or ''} {candidate['famille'] or ''}".strip() for candidate in candidates]
        embeddings = embedding_model.encode([dpgf_text] + candidate_texts)
        dpgf_embedding = embeddings[0]
        candidate_embeddings = embeddings[1:]
        semantic_weight, text_weight = self.poids_matching_ia()
        results = []
        diagnostic = []
        for candidate, embedding in zip(candidates, candidate_embeddings):
            semantic_score = self._cosine_similarity_score(dpgf_embedding, embedding)
            text_score, text_details = self._score_details(section, candidate)
            final = min(100, max(0, (semantic_score * float(semantic_weight)) + (text_score * float(text_weight))))
            diagnostic.append((final, semantic_score, text_score, candidate))
            if Decimal(str(round(final, 2))) >= score_minimum:
                results.append(self._to_result(candidate, Decimal(str(round(final, 2)))))
        diagnostic.sort(key=lambda item: item[0], reverse=True)
        logger.info(
            "Matching IA: section_id=%s candidats=%s top3=%s",
            section.id,
            len(candidates),
            [
                {
                    "score": round(final, 2),
                    "semantic": round(semantic, 2),
                    "text": round(textual, 2),
                    "code": candidate["code"],
                    "designation": candidate["designation"],
                }
                for final, semantic, textual, candidate in diagnostic[:3]
            ],
        )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:10]

    def _score_candidates_ia_with_embeddings(self, section: SectionProjet, candidates_with_embeddings: List[tuple], score_minimum: Decimal, model) -> List[MatchingResult]:
        if not candidates_with_embeddings:
            return []
        dpgf_embedding = model.encode([section.libelle or ""])[0]
        semantic_weight, text_weight = self.poids_matching_ia()
        results = []
        diagnostic = []
        for candidate, embedding in candidates_with_embeddings:
            semantic_score = self._cosine_similarity_score(dpgf_embedding, embedding)
            text_score, _text_details = self._score_details(section, candidate)
            final = min(100, max(0, (semantic_score * float(semantic_weight)) + (text_score * float(text_weight))))
            diagnostic.append((final, semantic_score, text_score, candidate))
            if Decimal(str(round(final, 2))) >= score_minimum:
                results.append(self._to_result(candidate, Decimal(str(round(final, 2)))))
        diagnostic.sort(key=lambda item: item[0], reverse=True)
        logger.info(
            "Matching IA: section_id=%s candidats=%s top3=%s",
            section.id,
            len(candidates_with_embeddings),
            [
                {
                    "score": round(final, 2),
                    "semantic": round(semantic, 2),
                    "text": round(textual, 2),
                    "code": candidate["code"],
                    "designation": candidate["designation"],
                }
                for final, semantic, textual, candidate in diagnostic[:3]
            ],
        )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:10]

    def _score_details(self, section: SectionProjet, candidate: dict) -> tuple[float, dict]:
        candidate_text = f"{candidate['designation']} {candidate['famille']}"
        dpgf_text = self._search_text(section.libelle)
        biblio_text = self._search_text(candidate_text)
        score_token_set = fuzz.token_set_ratio(dpgf_text, biblio_text)
        score_partial = fuzz.partial_ratio(dpgf_text, biblio_text)
        score_token_sort = fuzz.token_sort_ratio(dpgf_text, biblio_text)
        text_score = (
            score_token_set * TOKEN_SET_WEIGHT
            + score_partial * PARTIAL_WEIGHT
            + score_token_sort * TOKEN_SORT_WEIGHT
        )
        score = text_score

        if self.normaliser_unite(section.unite) and self.normaliser_unite(section.unite) == self.normaliser_unite(candidate["unite"]):
            score += UNIT_MATCH_BONUS
        elif section.unite and candidate["unite"]:
            score -= UNIT_MISMATCH_PENALTY

        famille_words = set(self._search_text(candidate["famille"]).split("_"))
        section_words = set(dpgf_text.split("_"))
        if famille_words and section_words and famille_words.intersection(section_words):
            score += FAMILY_MATCH_BONUS

        dpgf_important = self._technical_words(dpgf_text)
        biblio_important = self._technical_words(biblio_text)
        common_technical_words = dpgf_important.intersection(biblio_important)
        if dpgf_important and biblio_important and not common_technical_words:
            score -= NO_COMMON_TECHNICAL_WORD_PENALTY

        dpgf_dimensions = self._dimension_values(section.libelle)
        biblio_dimensions = self._dimension_values(candidate_text)
        common_dimensions = dpgf_dimensions.intersection(biblio_dimensions)
        if dpgf_dimensions and biblio_dimensions:
            if common_dimensions:
                score += DIMENSION_EXACT_BONUS
            else:
                score -= DIMENSION_MISMATCH_PENALTY

        final_score = max(0, min(100, score))
        return final_score, {
            "dpgf_text": dpgf_text,
            "biblio_text": biblio_text,
            "token_set": round(score_token_set, 2),
            "partial": round(score_partial, 2),
            "token_sort": round(score_token_sort, 2),
            "score_textuel": round(text_score, 2),
            "mots_techniques_communs": sorted(common_technical_words),
            "dimensions_communes": sorted(common_dimensions),
            "score_final": round(final_score, 2),
        }

    def _bibliotheque_proche_lot(self, corps_metier: str, section: SectionProjet) -> bool:
        corpus = self._slug(f"{section.feuille_source} {self._top_parent_label(section)}")
        metier_words = set(self._slug(corps_metier).split("_"))
        corpus_words = set(corpus.split("_"))
        return bool(metier_words.intersection(corpus_words))

    def _filter_candidates_by_metier(self, section: SectionProjet, candidates: List[dict]) -> List[dict]:
        corpus = self._slug(f"{section.feuille_source} {self._top_parent_label(section)}")
        corpus_words = set(corpus.split("_"))
        return [
            candidate for candidate in candidates
            if candidate.get("_metier_words", set()).intersection(corpus_words)
        ]

    def _top_parent_label(self, section: SectionProjet) -> str:
        sections = self._sections_cache_by_projet.get(section.projet_id)
        if sections is None:
            sections = {s.id: s for s in self.section_repo.get_by_projet(section.projet_id)}
            self._sections_cache_by_projet[section.projet_id] = sections
        current = section
        while current.parent_id and current.parent_id in sections:
            current = sections[current.parent_id]
        return current.libelle

    def _catalogue_candidates(self) -> List[dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    o.id AS ouvrage_bibliotheque_id,
                    b.id AS bibliotheque_id,
                    o.code,
                    o.designation,
                    o.famille,
                    o.unite,
                    o.debourse_sec_import,
                    o.pv_eg_ht_import,
                    b.nom AS bibliotheque_nom,
                    b.corps_metier
                FROM ouvrages_bibliotheque o
                JOIN bibliotheques b ON b.id = o.bibliotheque_id
                WHERE o.actif = 1 AND b.actif = 1
                ORDER BY b.nom, o.designation
                """
            ).fetchall()
            candidates = [dict(row) for row in rows]
            for candidate in candidates:
                candidate["_keywords"] = self._keywords(f"{candidate['designation']} {candidate['famille']}")
                candidate["_metier_words"] = set(self._slug(candidate["corps_metier"]).split("_"))
            return candidates

    def _candidates_for_ai_section(self, section: SectionProjet, rechercher_toutes_bibliotheques: bool) -> List[dict]:
        candidates = self._catalogue_candidates()
        if rechercher_toutes_bibliotheques:
            return candidates
        active_project_ids = self._active_project_library_ids(section.projet_id)
        if active_project_ids is not None:
            return [candidate for candidate in candidates if candidate["bibliotheque_id"] in active_project_ids]
        return self._filter_candidates_by_metier(section, candidates)

    def _filter_ai_candidates_with_embeddings(self, section: SectionProjet, candidates_with_embeddings: List[tuple], rechercher_toutes_bibliotheques: bool, active_project_ids: Optional[set[int]]) -> List[tuple]:
        if rechercher_toutes_bibliotheques:
            return candidates_with_embeddings
        if active_project_ids is not None:
            return [
                (candidate, embedding)
                for candidate, embedding in candidates_with_embeddings
                if candidate["bibliotheque_id"] in active_project_ids
            ]
        filtered_candidates = self._filter_candidates_by_metier(section, [candidate for candidate, _embedding in candidates_with_embeddings])
        filtered_ids = {candidate["ouvrage_bibliotheque_id"] for candidate in filtered_candidates}
        return [
            (candidate, embedding)
            for candidate, embedding in candidates_with_embeddings
            if candidate["ouvrage_bibliotheque_id"] in filtered_ids
        ]

    def _commit_pending(self, conn, pending: list[tuple[int, MatchingResult]]) -> int:
        count = 0
        for section_id, result in pending:
            self.correspondance_repo.upsert_proposition_conn(
                conn,
                section_id,
                result.ouvrage_bibliotheque_id,
                result.score,
                "automatique",
            )
            count += 1
        return count

    def _build_candidate_keyword_index(self, candidates: List[dict]) -> dict[str, list[dict]]:
        index = {}
        for candidate in candidates:
            for keyword in candidate.get("_keywords", set()):
                index.setdefault(keyword, []).append(candidate)
        return index

    def _prefilter_candidates_by_keywords(self, section: SectionProjet, candidates: List[dict], candidate_index: Optional[dict[str, list[dict]]] = None) -> List[dict]:
        section_keywords = self._keywords(section.libelle)
        if not section_keywords:
            return []
        if candidate_index:
            candidate_ids = {candidate["ouvrage_bibliotheque_id"] for candidate in candidates}
            selected = {}
            for keyword in section_keywords:
                for candidate in candidate_index.get(keyword, []):
                    if candidate["ouvrage_bibliotheque_id"] in candidate_ids:
                        selected[candidate["ouvrage_bibliotheque_id"]] = candidate
            filtered = list(selected.values())
        else:
            filtered = [
                candidate for candidate in candidates
                if section_keywords.intersection(candidate.get("_keywords", set()))
            ]
        logger.debug(
            "Matching DPGF: prefiltre mots cles section_id=%s avant=%s apres=%s mots=%s",
            section.id,
            len(candidates),
            len(filtered),
            sorted(section_keywords),
        )
        return filtered if filtered else candidates

    def _get_section(self, section_id: int) -> Optional[SectionProjet]:
        return self.section_repo.get_by_id(section_id)

    def _active_project_libraries_count(self, projet_id: int) -> Optional[int]:
        with self.db.get_connection() as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'bibliotheques_projet'"
            ).fetchone()
            if not table:
                return None
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT bp.bibliotheque_id)
                FROM bibliotheques_projet bp
                JOIN bibliotheques b ON b.id = bp.bibliotheque_id
                WHERE bp.projet_id = ? AND b.actif = 1
                """,
                (projet_id,),
            ).fetchone()
            return int(row[0])

    def _active_project_library_ids(self, projet_id: int) -> Optional[set[int]]:
        with self.db.get_connection() as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'bibliotheques_projet'"
            ).fetchone()
            if not table:
                return None
            rows = conn.execute(
                """
                SELECT DISTINCT bp.bibliotheque_id
                FROM bibliotheques_projet bp
                JOIN bibliotheques b ON b.id = bp.bibliotheque_id
                WHERE bp.projet_id = ? AND b.actif = 1
                """,
                (projet_id,),
            ).fetchall()
            return {int(row[0]) for row in rows}

    def _to_result(self, candidate: dict, score: Decimal) -> MatchingResult:
        return MatchingResult(
            ouvrage_bibliotheque_id=candidate["ouvrage_bibliotheque_id"],
            score=score,
            code=candidate["code"] or "",
            designation=candidate["designation"] or "",
            famille=candidate["famille"] or "",
            unite=candidate["unite"] or "",
            debourse_sec_import=candidate["debourse_sec_import"],
            pv_eg_ht_import=candidate["pv_eg_ht_import"],
            bibliotheque_nom=candidate["bibliotheque_nom"] or "",
            corps_metier=candidate["corps_metier"] or "",
        )

    def _get_embedding_model(self):
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "La recherche IA nécessite la dépendance Python 'sentence-transformers'. "
                    "Installez les dépendances du projet avant de lancer cette recherche."
                ) from exc
            logger.info("Matching IA: chargement du modèle %s", DEFAULT_AI_MODEL_NAME)
            self._embedding_model = SentenceTransformer(DEFAULT_AI_MODEL_NAME)
        return self._embedding_model

    def _cosine_similarity_score(self, left, right) -> float:
        left_values = [float(value) for value in left]
        right_values = [float(value) for value in right]
        numerator = sum(a * b for a, b in zip(left_values, right_values))
        left_norm = math.sqrt(sum(a * a for a in left_values))
        right_norm = math.sqrt(sum(b * b for b in right_values))
        if left_norm == 0 or right_norm == 0:
            return 0
        similarity = numerator / (left_norm * right_norm)
        return max(0, min(100, ((similarity + 1) / 2) * 100))

    def _decimal_param(self, cle: str, default: Decimal, description: str) -> Decimal:
        param = self.parametre_service.obtenir_parametre(cle)
        if not param:
            self.parametre_service.creer_ou_modifier_parametre(cle, str(default), "decimal", "ratio", description)
            return default
        try:
            return Decimal(str(param.valeur))
        except Exception:
            return default

    def _slug(self, text: str) -> str:
        return self._slugger.slugify(text or "")

    def _search_text(self, text: str) -> str:
        tokens = [token for token in self._slug(text).split("_") if token and token not in STOPWORDS_FR]
        return "_".join(tokens)

    def _keywords(self, text: str) -> set[str]:
        return {
            token for token in self._search_text(text).split("_")
            if len(token) >= 4 or any(char.isdigit() for char in token)
        }

    def _technical_words(self, normalized_text: str) -> set[str]:
        tokens = set()
        for token in normalized_text.split("_"):
            if not token or token in STOPWORDS_FR:
                continue
            if any(char.isdigit() for char in token) or len(token) >= 4:
                tokens.add(token)
        return tokens

    def _dimension_values(self, text: str) -> set[str]:
        normalized = str(text or "").lower().replace(",", ".")
        dimensions = set()
        for left, right in re.findall(r"\b(\d{2,3})\s*[/x]\s*(\d{2,3})\b", normalized):
            dimensions.add(f"{left}/{right}")
        return dimensions
