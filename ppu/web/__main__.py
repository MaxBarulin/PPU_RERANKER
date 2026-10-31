import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Веб-интерфейс проверки ППУ")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--index", help="папка индекса (по умолчанию data/index)")
    args = parser.parse_args()
    if args.index:
        os.environ["PPU_INDEX"] = args.index
    uvicorn.run("ppu.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
