"""Extract AI responses from Perplexity's web interface."""

from importlib import metadata

from .config import ClientConfig, ConversationConfig
from .core import Conversation, Perplexity
from .enums import CitationMode, LogLevel, SearchFocus, SourceFocus, TimeRange
from .exceptions import (
    AuthenticationError,
    FileUploadError,
    FileValidationError,
    HTTPError,
    PerplexityError,
    RateLimitError,
    ResearchClarifyingQuestionsError,
    ResponseParsingError,
    StreamingError,
)
from .models import MODELS, Model
from .types import Coordinates, FileInput, Response, SearchResultItem


ConversationConfig.model_rebuild()


__version__: str = metadata.version("perplexity-webui-scraper")
__all__: list[str] = [
    "MODELS",
    "AuthenticationError",
    "CitationMode",
    "ClientConfig",
    "Conversation",
    "ConversationConfig",
    "Coordinates",
    "FileInput",
    "FileUploadError",
    "FileValidationError",
    "HTTPError",
    "LogLevel",
    "Model",
    "Perplexity",
    "PerplexityError",
    "RateLimitError",
    "ResearchClarifyingQuestionsError",
    "Response",
    "ResponseParsingError",
    "SearchFocus",
    "SearchResultItem",
    "SourceFocus",
    "StreamingError",
    "TimeRange",
]
