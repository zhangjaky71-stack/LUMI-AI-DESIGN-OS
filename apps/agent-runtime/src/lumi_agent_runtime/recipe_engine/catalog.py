P0_DETERMINISTIC_SERVICES = frozenset(
    {
        "artifact.finalize",
        "campaign.finalize",
        "project.finalize",
        "quality.evaluate",
    }
)

P0_MEDIA_OPERATIONS = frozenset(
    {
        "image.generate",
        "image.edit",
        "video.generate",
        "export.render",
    }
)
