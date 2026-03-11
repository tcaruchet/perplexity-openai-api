"""Extract AI responses from Perplexity's web interface."""

from importlib.metadata import version

from .config import ClientConfig, ConversationConfig
from .core import Conversation, Perplexity
from .enums import CitationMode, SearchFocus, SourceFocus, TimeRange
from .exceptions import (
    AuthenticationError,
    FileUploadError,
    FileValidationError,
    PerplexityError,
    RateLimitError,
)
from .models import Model, Models
from .types import Coordinates, Response, SearchResultItem
from .fetch_models import PerplexityModelsFetcher, ModelInfo, get_available_models


__version__: str = version("perplexity-webui-scraper")
__all__: list[str] = [
    "AuthenticationError",
    "CitationMode",
    "ClientConfig",
    "Conversation",
    "ConversationConfig",
    "Coordinates",
    "FileUploadError",
    "FileValidationError",
    "get_available_models",
    "Model",
    "ModelInfo",
    "Models",
    "Perplexity",
    "PerplexityError",
    "PerplexityModelsFetcher",
    "RateLimitError",
    "Response",
    "SearchFocus",
    "SearchResultItem",
    "SourceFocus",
    "TimeRange",
]
