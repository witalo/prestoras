# Quita del repositorio (índice) todo lo que ahora está en .gitignore.
# No borra archivos del disco, solo deja de trackearlos.
# Ejecutar desde la raíz del proyecto: .\git-clean-ignore.ps1

Set-Location $PSScriptRoot
Write-Host "Quitando del indice archivos/carpetas ignorados por .gitignore..." -ForegroundColor Yellow
git rm -r --cached . 2>$null
git add .
Write-Host "Listo. Revisa con: git status" -ForegroundColor Green
Write-Host "Luego: git commit -m \"Limpiar archivos ignorados del repositorio\"" -ForegroundColor Cyan
