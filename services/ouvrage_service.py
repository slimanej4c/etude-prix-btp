from typing import List
from repositories.ouvrage_bibliotheque_repository import OuvrageBibliothequeRepository
from models.entites import OuvrageBibliotheque

class OuvrageService:
    def __init__(self, repository: OuvrageBibliothequeRepository):
        self.repository = repository

    def lister_ouvrages_bibliotheque(self, bibliotheque_id: int) -> List[OuvrageBibliotheque]:
        return self.repository.get_all_by_bibliotheque(bibliotheque_id)

    def creer_ouvrage(self, ouvrage: OuvrageBibliotheque) -> int:
        if not ouvrage.designation:
            raise ValueError("La désignation de l'ouvrage est obligatoire.")
        if not ouvrage.unite:
            raise ValueError("L'unité de l'ouvrage est obligatoire.")
        return self.repository.create(ouvrage)

    def modifier_ouvrage(self, ouvrage: OuvrageBibliotheque):
        if ouvrage.id is None:
            raise ValueError("L'identifiant de l'ouvrage est obligatoire.")
        if not ouvrage.designation:
            raise ValueError("La désignation de l'ouvrage est obligatoire.")
        if not ouvrage.unite:
            raise ValueError("L'unité de l'ouvrage est obligatoire.")
        self.repository.update(ouvrage)

    def supprimer_ouvrage(self, ouvrage_id: int):
        self.repository.delete(ouvrage_id)
