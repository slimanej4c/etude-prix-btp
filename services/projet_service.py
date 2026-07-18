from typing import List, Optional
from repositories.projet_repository import ProjetRepository
from models.entites import Projet

class ProjetService:
    def __init__(self, repository: ProjetRepository):
        self.repository = repository

    def creer_projet(self, nom: str, client: str = "", reference: str = "", statut: str = "Nouveau") -> int:
        if not nom:
            raise ValueError("Le nom du projet est obligatoire.")
            
        projet = Projet(
            id=None,
            nom=nom,
            client=client,
            reference=reference,
            statut=statut,
            date_creation="",
            date_modification=""
        )
        return self.repository.create(projet)

    def obtenir_projet(self, id: int) -> Optional[Projet]:
        return self.repository.get_by_id(id)

    def lister_projets(self) -> List[Projet]:
        return self.repository.get_all()

    def modifier_projet(self, id: int, nom: str, client: str, reference: str, statut: str):
        if not nom:
            raise ValueError("Le nom du projet est obligatoire.")
            
        projet = self.repository.get_by_id(id)
        if not projet:
            raise ValueError("Projet introuvable.")
            
        projet.nom = nom
        projet.client = client
        projet.reference = reference
        projet.statut = statut
        self.repository.update(projet)

    def supprimer_projet(self, id: int):
        self.repository.delete(id)
