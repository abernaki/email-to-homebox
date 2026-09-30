"""Homebox operation errors shared between the client and receipt pipeline."""


class PartialEntityUpdateError(RuntimeError):
    """An entity was created, but its required follow-up update failed."""

    def __init__(self, entity_id):
        self.entity_id = entity_id
        super().__init__(
            f"Homebox entity {entity_id} was created but its required purchase update failed"
        )
