import logging
import multiprocessing
import time

import click

from runners import (
    ServerRunner,
    ServicesRunner,
    RunnerConfig,
    run_runner,
)


@click.group()
def http():
    """Manages the HTTP server"""
    pass


@http.command(name="run")
def http_run():
    logger = logging.getLogger("main")

    configs = (
        RunnerConfig(cls=ServicesRunner),
        RunnerConfig(cls=ServerRunner, kwargs={"host": "0.0.0.0", "port": 8000}),
    )

    ps = [
        multiprocessing.Process(target=run_runner, args=(conf,), name=conf.name)
        for conf in configs
    ]

    for p in ps:
        logger.info(f"Process '{p.name}' has started")
        p.start()

    try:
        while True:
            for p in ps:
                if not p.is_alive():
                    logger.info(f"Process '{p.name}' has died")
                    raise Exception

            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Gracefully shutting down")
    finally:
        logger.info("Shutting down processes")

        for p in ps:
            logger.info(f"Shutting down process '{p.name}'")
            p.kill()
            p.join(timeout=10)
            logger.info(f"Process '{p.name}' shut down successfully")

        logger.info("All processes shut down successfully.")
