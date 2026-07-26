from django.conf import settings

from .base import InferenceBackend, InferenceResult

__all__ = ["InferenceBackend", "InferenceResult", "get_inference_backend"]

_BACKENDS = {
    "openai_compatible": "evaluate.backends.openai_compatible.OpenAICompatibleBackend",
}


def get_inference_backend() -> InferenceBackend:
    from django.utils.module_loading import import_string

    backend_path = _BACKENDS.get(settings.INFERENCE_BACKEND, settings.INFERENCE_BACKEND)
    backend_cls = import_string(backend_path)
    return backend_cls()
