"""
Last.FM adapter

Collaborative signal


"""

if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    key = os.environ.get("LASTFM_API_KEY")
    # error handle no env
    if not key:
        raise SystemExit("No LASTFM_API_KEY in .env")
