import click
from cli.commands import db, engine, http


@click.group()
def cli():
    pass


cli.add_command(db)
cli.add_command(engine)
cli.add_command(http)
