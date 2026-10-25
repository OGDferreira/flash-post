# Script para remover ícones antigos do Falcon
# Execute este script quando estiver pronto para limpar os arquivos antigos

# Ícones antigos do Falcon que devem ser removidos:
FALCON_FILES=(
  "frontend/public/brand/falconadm-emblem-128.webp"
  "frontend/public/brand/falconadm-emblem-256.webp"
  "frontend/public/brand/falconadm-emblem-512.png"
  "frontend/public/brand/falconadm-emblem-512.webp"
  "frontend/public/brand/falconbot-emblem-128.webp"
  "frontend/public/brand/falconbot-emblem-256.webp"
  "frontend/public/brand/falconbot-emblem-512.png"
  "frontend/public/brand/falconbot-emblem-512.webp"
  "frontend/public/brand/falconbot-icon-192.png"
  "frontend/public/brand/falconbot-lockup-dark.webp"
  "frontend/public/brand/falconbot-lockup-light.webp"
  "frontend/public/brand/falconbot-wordmark-dark.webp"
  "frontend/public/brand/falconbot-wordmark-light.webp"
  "frontend/public/brand/falconpost-emblem-128.webp"
  "frontend/public/brand/falconpost-emblem-256.webp"
  "frontend/public/brand/falconpost-emblem-512.png"
  "frontend/public/brand/falconpost-emblem-512.webp"
  "frontend/public/brand/falconpost-lockup-dark.webp"
  "frontend/public/brand/falconpost-lockup-light.webp"
  "frontend/public/brand/falconpost-wordmark-dark.webp"
  "frontend/public/brand/falconpost-wordmark-light.webp"
)

echo "Os seguintes arquivos antigos do Falcon estão presentes:"
for file in "${FALCON_FILES[@]}"; do
  if [ -f "$file" ]; then
    echo "  - $file"
  fi
done

echo ""
echo "Para remover esses arquivos, execute:"
echo "rm ${FALCON_FILES[@]}"
