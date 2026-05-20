import asyncio
import time
import logging
from orchestrator.config import settings
from orchestrator.spawner import terminate_container

logger = logging.getLogger("orchestrator.reaper")

# Thread-safe in-memory session registry
# Format: { session_id: { "container_name": ..., "workspace_dir": ..., "last_accessed": ..., "target_url": ..., "internal_key": ... } }
sessions = {}

async def session_reaper_loop(interval_seconds: int = 30):
    """
    Periodically scans active sessions and prunes idle ones that have exceeded the inactivity timeout.
    """
    logger.info("Initializing session reaper background task (interval=%ds, timeout=%ds)...", 
                interval_seconds, settings.session_timeout_seconds)
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = time.time()
            expired_ids = []
            
            # Identify expired sessions
            for session_id, session_data in list(sessions.items()):
                inactive_duration = now - session_data["last_accessed"]
                if inactive_duration > settings.session_timeout_seconds:
                    logger.info("Session %s idle for %ds (exceeded timeout of %ds), pruning...", 
                                session_id, int(inactive_duration), settings.session_timeout_seconds)
                    expired_ids.append(session_id)
            
            # Prune identified sessions
            for session_id in expired_ids:
                # Remove from registry first to prevent concurrent API proxy requests during teardown
                session = sessions.pop(session_id, None)
                if session:
                    try:
                        # Perform docker stop/remove and folder rmtree synchronously in executor if blocking
                        await asyncio.to_thread(
                            terminate_container,
                            container_name=session["container_name"],
                            workspace_dir=session["workspace_dir"]
                        )
                        logger.info("Successfully reaped session %s.", session_id)
                    except Exception as e:
                        logger.error("Failed to reap session %s: %s", session_id, str(e))
                        
        except asyncio.CancelledError:
            logger.info("Session reaper loop cancelled.")
            break
        except Exception as e:
            logger.error("Error in session reaper loop: %s", str(e))
