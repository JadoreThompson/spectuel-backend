import logging
import multiprocessing
import time

import click

from runners import run_runner, ServerRunner, OrderBookSnapshotRunner, EngineHeartbeatRunner


@click.group()
def http():
    """Manages the HTTP server"""
    pass


@http.command(name="run")
def http_run():
    logger = logging.getLogger("main")

    configs = (
        (ServerRunner, (), {"host": "0.0.0.0", "port": 8000}),
        # (OrderBookSnapshotRunner, (), {}),
        # (EngineHeartbeatRunner, (), {}),
    )

    ps = [
        multiprocessing.Process(
            target=run_runner,
            args=(runner_cls, *args),
            kwargs=kwargs,
            name=runner_cls.__name__,
        )
        for runner_cls, args, kwargs in configs
    ]

    for p in ps:
        logger.info(f"Process '{p.name}' has started")
        p.start()

    try:
        while True:
            for ind, p in enumerate(ps):
                if not p.is_alive():
                    logger.info(f"Process '{p.name}' has died")
                    # p.kill()
                    # p.join()
                    # runner_cls, args, kwargs = configs[ind]
                    # ps[ind] = multiprocessing.Process(
                    #     target=run_runner, args=(runner_cls, *args), kwargs=kwargs, name=runner_cls.__name__
                    # )
                    # ps[ind].start()

                    # logger.info("[INFO]: Restarted process for", p.name)
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
