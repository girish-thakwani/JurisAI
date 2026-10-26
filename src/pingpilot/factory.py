"""Add a new source or channel: implement the base class, register it here."""
from .exceptions import ConfigError


def build_source(s):
    if s.source == "sheet":
        from .sources.google_sheet import GoogleSheetSource

        return GoogleSheetSource(s.sheet_url, s.creds_file, s.max_offline_wait)
    if s.source == "csv":
        from .sources.csv_source import CsvSource

        return CsvSource(s.csv_path)
    raise ConfigError(f"Unknown SOURCE '{s.source}' (sheet | csv)")


def build_channel(s):
    if s.channel == "whatsapp_web":
        from .channels.whatsapp_web import WhatsAppWebChannel

        return WhatsAppWebChannel(s)
    if s.channel == "dry_run":
        from .channels.dry_run import DryRunChannel

        return DryRunChannel()
    raise ConfigError(f"Unknown CHANNEL '{s.channel}' (whatsapp_web | dry_run)")
