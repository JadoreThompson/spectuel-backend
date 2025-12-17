import logging
import click

from engine.runners import EventHandlerRunner, ListenerRunner

@click.group()
def engine():
    """Manages the engine"""
    pass


@engine.command(name='run')
def engine_run():
    logger = logging.getLogger("main")
    queue = Queue()
    watchdog_ts = Value("i", int(time.time()))

    configs = (
        (EventHandlerRunner, (), {}),
        (ListenerRunner, (queue, watchdog_ts), {}),
        # (HeartbeatRunner, (queue, watchdog_ts), {}),
    )

    ps = [
        Process(
            target=run_runner,
            args=(runner_cls, *args),
            kwargs=kwargs,
            name=runner_cls.__name__,
        )
        for runner_cls, args, kwargs in configs
    ]

    for p in ps:
        p.start()

    try:
        while True:
            for i, p in enumerate(ps):
                if not p.is_alive():
                    raise RuntimeError(f"Process '{p.name}' has died unexpectedly!")
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down all processes.")
    finally:
        for p in ps:
            if p.is_alive():
                logger.info(f"Shutting down process '{p.name}'...")
                p.kill()
                p.join(timeout=10)

        logger.info("All processes shut down.")