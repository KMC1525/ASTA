"""Teste de carga da stable-diffusion.cpp em um processo À PARTE: `python -m asta.canvas.sd_probe '<json dos argumentos>'`.
Quando a biblioteca não reconhece o modelo, ela pode derrubar o processo (falha de segmentação). Aqui isso só derruba este teste — o ASTA lê o código de saída:
0 = carregou, 3 = a biblioteca recusou o modelo, outro valor (ou negativo = sinal) = o processo caiu."""
import json
import sys


def main(argv) -> int:
    kw = json.loads(argv[1]) if len(argv) > 1 else {}
    import stable_diffusion_cpp as sdc

    sd = sdc.StableDiffusion(**kw)
    ctx = getattr(getattr(sd, "_model", None), "model", 1)
    return 0 if ctx else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
