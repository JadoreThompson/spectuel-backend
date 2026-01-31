from .runner_config import RunnerConfig


def run_runner(runner_config: RunnerConfig) -> None:
    runner = runner_config.cls(*runner_config.args, **runner_config.kwargs)
    runner.run()
