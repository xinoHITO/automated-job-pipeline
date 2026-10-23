import asyncio

import typer
from . import globals
from . import hiring_profile
app = typer.Typer(help="Config-driven job discovery pipeline")


@app.command()
def run(
    write_cover_letters: bool = typer.Option(False, "--write-cover","-w", help="Write cover letters for each job that passed screening"),    
    max_days: int = typer.Option(15,"--max-days","-d", help="Ignore postings older than N days"),
    hiring_profile: str = typer.Option("test","--profile","-p", help="Which profile to use a filter"),
    send_notification: bool = typer.Option(False,"--notification","-n", help="Wether to send a discord notification when pipeline ends"),
):
    from . import JobBot
    asyncio.run(
        JobBot.main(max_days,hiring_profile,write_cover_letters,send_notification)
    ) 

@app.command()
def scrape(    
    max_days: int = typer.Option(15,"--max-days","-d", help="Ignore postings older than N days"),    
    profiling: bool = typer.Option(False,"--profiling","-e", help="Wether to profile the app"),
    send_notification: bool = typer.Option(False,"--notification","-n", help="Wether to send a discord notification when scraping ends"),
):
    from . import JobBot
    if profiling:
        from . import profiler
        profiler.start_profiling()
        try:
            asyncio.run(
                JobBot.scrape(max_days)
            )
        finally:
            profiler.end_profiling()
    else:
        asyncio.run(
            JobBot.scrape(max_days)
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