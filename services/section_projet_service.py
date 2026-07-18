from typing import List

from models.entites import SectionProjet
from repositories.section_projet_repository import SectionProjetRepository


class SectionProjetService:
    def __init__(self, repository: SectionProjetRepository):
        self.repository = repository

    def lister_sections(self, projet_id: int) -> List[SectionProjet]:
        return self.repository.get_by_projet(projet_id)

    def compter_sections(self, projet_id: int) -> int:
        return self.repository.count_by_projet(projet_id)
