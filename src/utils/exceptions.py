class ETLError(Exception):
    """Base exception for ETL failures."""
    pass

class FetchError(ETLError):
    pass

class DBError(ETLError):
    pass
