import asyncio
import multiprocessing

from stream import main

def start(*args, **kwargs):
    """
    Start the stream proxy server, compatible with positional and keyword arguments

    Positional argument mode (compatible with reference file):
        start(queue, port, proxy)

    Keyword argument mode:
        start(queue=queue, port=port, proxy=proxy)
    """
    if args:
        # Positional argument mode (compatible with reference file)
        queue = args[0] if len(args) > 0 else None
        port = args[1] if len(args) > 1 else None
        proxy = args[2] if len(args) > 2 else None
    else:
        # Keyword argument mode
        queue = kwargs.get('queue', None)
        port = kwargs.get('port', None)
        proxy = kwargs.get('proxy', None)

    asyncio.run(main.builtin(queue=queue, port=port, proxy=proxy))