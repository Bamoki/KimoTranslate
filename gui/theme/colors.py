"""Design tokens: colores. Dark por defecto; light preparado."""

DARK = {
    "background": "#1A1B26",
    "surface": "#24283B",
    "surface_elevated": "#2F354D",
    "surface_hover": "#3A415C",
    "border": "#3B4261",
    "text": "#C0CAF5",
    "text_secondary": "#9AA5CE",
    "text_muted": "#565F89",
    "accent": "#7AA2F7",
    "accent_hover": "#5D7FD6",
    "success": "#9ECE6A",
    "warning": "#E0AF68",
    "error": "#F7768E",
    "info": "#7DCFFF",
}

LIGHT = {
    "background": "#F4F4F6",
    "surface": "#FFFFFF",
    "surface_elevated": "#EDEDF2",
    "surface_hover": "#E2E2EA",
    "border": "#D4D4DE",
    "text": "#1A1B26",
    "text_secondary": "#4A4E69",
    "text_muted": "#8A8FA8",
    "accent": "#3457B1",
    "accent_hover": "#27437F",
    "success": "#4E8A2A",
    "warning": "#B07818",
    "error": "#C53B5A",
    "info": "#1E7FA8",
}

# Semántica de estado (igual en ambos temas; no solo color: ver badges.py).
STATUS = {
    "ONLINE": "success",
    "COMPLETED": "success",
    "VALIDATED": "success",
    "LOCALIZED": "success",
    "PASS": "success",
    "RUNNING": "info",
    "QUEUED": "info",
    "CONNECTING": "info",
    "WARNING": "warning",
    "REVIEW_REQUIRED": "warning",
    "SHRUNK": "warning",
    "OFFLINE": "error",
    "FAILED": "error",
    "ERROR": "error",
    "OVERFLOW": "error",
    "REJECTED": "error",
}
