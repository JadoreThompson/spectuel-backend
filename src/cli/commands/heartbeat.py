import logging
import multiprocessing
import time

import click

from runners import HeartbeatServerRunner, RunnerConfig, run_runner


@click.group()
def heartbeat():
    """Manages the heartbeat server"""
    pass


@heartbeat.command(name="run")
def heartbeat_run():
    logger = logging.getLogger("main")

    config = RunnerConfig(cls=HeartbeatServerRunner)

    p = multiprocessing.Process(target=run_runner, args=(config,), name=config.name)

    logger.info(f"Process '{p.name}' has started")
    p.start()

    try:
        while True:
            if not p.is_alive():
                logger.info(f"Process '{p.name}' has died")
                raise Exception

            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Gracefully shutting down")
    finally:
        logger.info("Shutting down process")

        logger.info(f"Shutting down process '{p.name}'")
        p.kill()
        p.join(timeout=10)
        logger.info(f"Process '{p.name}' shut down successfully")

        logger.info("Heartbeat server shut down successfully.")
