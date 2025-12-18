import os
import subprocess
import sys
import click

from config import PROJECT_PATH
from infra.db import write_db_url_alembic_ini


@click.group()
def db():
    """Manages the DB"""
    pass


@db.command(name="upgrade")
def db_upgrade():
    fp = os.path.join(PROJECT_PATH, "alembic.ini")
    example_fp = os.path.join(PROJECT_PATH, "alembic.ini.example")

    if not os.path.exists(fp):
        if os.path.exists(example_fp):
            platform = sys.platform

            if platform == "windows":
                command = ["cmd", "/c", "copy", example_fp, fp]
            elif platform == "linux":
                command = ["cp", example_fp, fp]
            else:
                raise RuntimeError(f"Unsupported platform: {platform}")

            try:
                subprocess.run(command, check=True)
                click.echo("Created alembic.ini from example")
            except subprocess.CalledProcessError as e:
                click.echo(f"Failed to create alembic.ini: {e}", err=True)
                sys.exit(1)
        else:
            raise FileNotFoundError(
                "Failed to find alembic configuration file "
                "and the example configuration file"
            )

    write_db_url_alembic_ini()

    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        click.echo("Database upgraded successfully")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error upgrading database: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)
