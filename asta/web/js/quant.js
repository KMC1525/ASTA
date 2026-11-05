// Rótulos de qualidade das quantizações GGUF (a chave vem de asta/hf.py: parse_quant).
export const QUALITY_LABEL = { very_low: 'Qualidade muito baixa', low: 'Qualidade baixa', good: 'Boa qualidade', very_good: 'Muito boa qualidade', high: 'Quase igual ao original', lossless: 'Praticamente sem perdas', original: 'Original (enorme)' };
// Precisão dos modelos locais do Canvas (fp32/fp16/bf16): explicação mostrada na escolha, antes do download.
export const PREC_HINT = { fp32: 'Maior e mais lento, mas funciona em qualquer computador (inclusive só com CPU).', fp16: 'Metade do tamanho e da memória; ideal com placa de vídeo (GPU). Em CPU pode ser lento ou falhar.', bf16: 'Como o fp16, com a faixa de valores do fp32; pede um processador/GPU recente.' };
