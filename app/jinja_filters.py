from datetime import datetime

def timestamp_to_human(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %I:%M:%S %p")

def add_filters(templates):
    templates.env.filters['timestamp'] = timestamp_to_human

