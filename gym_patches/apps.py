import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

class PatchesConfig(AppConfig):
    name = 'gym_patches'
    verbose_name = 'Gym Patches'
    
    def ready(self):
        logger.info("Applying monkey patch for CourseMode")
        try:
            from .patches import apply_monkey_patch
            apply_monkey_patch()
            logger.info("Monkey patch applied successfully.")
        except Exception as e:
            logger.error(f"Failed to apply monkey patch: {e}")
