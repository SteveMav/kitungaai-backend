$serverRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$daphne = Join-Path $serverRoot ".venv\Scripts\daphne.exe"

if (-not (Test-Path -LiteralPath $daphne)) {
    throw "Daphne est introuvable. Installez les dépendances dans .venv avant de lancer le serveur."
}

if (-not $env:DJANGO_ALLOWED_HOSTS) {
    $env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1,stevemavuela,stevemavuela.local"
}

Set-Location $serverRoot
& $daphne -b 0.0.0.0 -p 8000 core.asgi:application
