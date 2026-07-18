from typing import List, Optional
from repositories.bibliotheque_repository import BibliothequeRepository
from models.entites import Bibliotheque

class BibliothequeService:
    def __init__(self, repository: BibliothequeRepository):
        self.repository = repository

    def creer_bibliotheque(self, nom: str, description: str = "", corps_metier: str = "", actif: bool = True) -> int:
        if not nom:
            raise ValueError("Le nom de la bibliothèque est obligatoire.")
            
        bibliotheque = Bibliotheque(
            id=None,
            nom=nom,
            description=description,
            corps_metier=corps_metier,
            actif=actif,
            date_creation="",
            date_modification=""
        )
        return self.repository.create(bibliotheque)

    def obtenir_bibliotheque(self, id: int) -> Optional[Bibliotheque]:
        return self.repository.get_by_id(id)

    def obtenir_par_nom(self, nom: str) -> Optional[Bibliotheque]:
        return self.repository.get_by_nom(nom)

    def lister_bibliotheques(self) -> List[Bibliotheque]:
        return self.repository.get_all()

    def modifier_bibliotheque(self, id: int, nom: str, description: str, corps_metier: str, actif: bool):
        if not nom:
            raise ValueError("Le nom de la bibliothèque est obligatoire.")
            
        bibliotheque = self.repository.get_by_id(id)
        if not bibliotheque:
            raise ValueError("Bibliothèque introuvable.")
            
        bibliotheque.nom = nom
        bibliotheque.description = description
        bibliotheque.corps_metier = corps_metier
        bibliotheque.actif = actif
        self.repository.update(bibliotheque)

    def supprimer_bibliotheque(self, id: int):
        self.repository.delete(id)
