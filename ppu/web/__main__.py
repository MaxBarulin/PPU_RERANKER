import argparse
import os

import uvicorn

from .. import config  # noqa: F401 - загружает .env (PPU_SSL_CERT/PPU_SSL_KEY)


def main():
    parser = argparse.ArgumentParser(description="Веб-интерфейс проверки ППУ")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--index", help="папка индекса (по умолчанию data/index)")
    # HTTPS: без него пароль администратора и тексты ППУ идут по сети открытым текстом
    parser.add_argument("--ssl-certfile", default=os.getenv("PPU_SSL_CERT") or None,
                        help="сертификат для HTTPS (или PPU_SSL_CERT в .env)")
    parser.add_argument("--ssl-keyfile", default=os.getenv("PPU_SSL_KEY") or None,
                        help="закрытый ключ для HTTPS (или PPU_SSL_KEY в .env)")
    args = parser.parse_args()
    if args.index:
        os.environ["PPU_INDEX"] = args.index
    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        parser.error("для HTTPS нужны и сертификат, и ключ (PPU_SSL_CERT и PPU_SSL_KEY)")
    # server_header=False - не сообщать всем, на чём работает сервер
    uvicorn.run("ppu.web.app:app", host=args.host, port=args.port, server_header=False,
                ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)


if __name__ == "__main__":
    main()
