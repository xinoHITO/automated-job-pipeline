import asyncio

import typer
from . import globals
app = typer.Typer(help="Config-driven job discovery pipeline")

@app.command()
def run(
    write_cover_letters: bool = typer.Option(False, "--write-cover","-w", help="Write cover letters for each job that passed screening"),    
    max_days: int = typer.Option(15,"--max-days","-d", help="Ignore postings older than N days"),
    scraping_rules_path: str = typer.Option(globals.DEFAULT_WEB_SCRAPING_CONFIG_PATH,"--scraping-rules","-s", help="Path for a scraping rules json file"),
    hiring_rules_path: str = typer.Option(globals.DEFAULT_HIRING_RULES_PATH,"--hiring-rules","-h", help="Path for a config json file that defines hiring rules"),
    profile: bool = typer.Option(False,"--profile","-p", help="Wether to profile the app"),
    send_notification: bool = typer.Option(False,"--notification","-n", help="Wether to send a discord notification when pipeline ends"),
):
    from . import JobBot
    if profile:
        from . import profiler
        profiler.start_profiling()
        try:
            asyncio.run(
                JobBot.main(max_days,write_cover_letters,scraping_rules_path,hiring_rules_path,send_notification)
            )
        finally:
            profiler.end_profiling()
    else:
        asyncio.run(
            JobBot.main(max_days,write_cover_letters,scraping_rules_path,hiring_rules_path,send_notification)
        )        
    
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
    enable_reload: bool = typer.Option(False, "--reload"),
):
    import uvicorn
    uvicorn.run("api:app", host=host, port=port, reload=enable_reload)

if __name__ == "__main__":
    app(args=["run","-d","10"])
    #app(args=["run","--write-cover","--max-days","10"])
    #app(args=["run","-w","-d","10"])