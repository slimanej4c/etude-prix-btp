from typing import List, Optional
from repositories.parametre_repository import ParametreRepository
from models.entites import ParametreGeneral

class ParametreService:
    def __init__(self, repository: ParametreRepository):
        self.repository = repository

    def creer_ou_modifier_parametre(self, cle: str, valeur: str, type_valeur: str, unite: str = "", description: str = ""):
        if not cle:
            raise ValueError("La clé du paramètre est obligatoire.")
        if type_valeur not in ['decimal', 'integer', 'boolean', 'text']:
            raise ValueError("Le type de valeur n'est pas valide.")

        existant = self.repository.get_by_cle(cle)
        
        parametre = ParametreGeneral(
            id=existant.id if existant else None,
            cle=cle,
            valeur=valeur,
            type_valeur=type_valeur,
            unite=unite,
            description=description,
            date_modification=""
        )

        if existant:
            self.repository.update(parametre)
        else:
            self.repository.create(parametre)

    def obtenir_parametre(self, cle: str) -> Optional[ParametreGeneral]:
        return self.repository.get_by_cle(cle)

    def lister_parametres(self) -> List[ParametreGeneral]:
        return self.repository.get_all()

    def supprimer_parametre(self, cle: str):
        self.repository.delete(cle)
