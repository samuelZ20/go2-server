#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intent_classifier.py — Classificação semântica de intenções.

Recebe texto (do Whisper) e identifica o comando por SIMILARIDADE SEMÂNTICA.
Zero hardcode: adicionar comando = adicionar frases ao INTENTS.
"""

import logging
import os
import unicodedata

log = logging.getLogger(__name__)

INTENT_THRESHOLD: float = float(os.getenv("INTENT_THRESHOLD", "0.65"))

# Escalável: adicionar comando novo = adicionar entrada aqui. Zero código.
INTENTS: dict[str, list[str]] = {
    "SIT": [
        "sentar", "senta", "sente aí", "pode sentar",
        "senta no chão", "abaixa o corpo", "fica sentado",
    ],
    "STAND": [
        "levantar", "levanta", "fica em pé", "levante-se",
        "pode levantar", "sobe", "fica de pé",
    ],
    "STRETCH": [
        "alongar", "faz alongamento", "se estica",
        "espreguiça", "estica o corpo", "alongamento",
    ],
    "HELLO": [
        "cumprimentar", "dá oi", "acena com a pata",
        "diz olá", "cumprimenta", "dá tchau",
        "levanta a pata para cumprimentar",
    ],
    "FINGER_HEART": [
        "faz um coração", "fazer coração", "coração com a pata",
        "gesto de coração", "faz coraçãozinho",
        "sinal de coração com os dedos", "desenha um coração",
    ],
    "WAG_TAIL": [
        "abana o rabo", "abanar o rabo", "balança o rabo",
        "mexe a cauda", "sacode o rabinho",
        "balança a caudinha", "agita a cauda",
    ],
}


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, sem pontuação."""
    nfd = unicodedata.normalize("NFD", text.lower())
    s = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())


class IntentClassifier:
    """
    Classificador por embeddings (sentence-transformers).

    Otimizações:
      ① device='cpu' forçado
      ② embeddings do INTENTS cacheados no __init__ (nunca por chamada)
      ③ warmup na inicialização (elimina cold start)
      ④ .item() extraído do tensor antes de comparar (evita RuntimeError)
    """

    def __init__(self, threshold: float = INTENT_THRESHOLD) -> None:
        self.threshold = threshold
        from sentence_transformers import SentenceTransformer, util

        self._util = util
        log.info("Carregando modelo semântico (MiniLM multilingual, cpu)...")
        self._model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2",
            device="cpu",
        )

        # ② Cacheia embeddings de todas as frases de exemplo, uma vez.
        self._phrases: list[str] = []
        self._phrase_intents: list[str] = []
        for intent, frases in INTENTS.items():
            for frase in frases:
                self._phrases.append(normalize(frase))
                self._phrase_intents.append(intent)

        self._embeddings = self._model.encode(
            self._phrases, convert_to_tensor=True, show_progress_bar=False
        )
        log.info("✓ %d embeddings cacheados (%d intenções).",
                 len(self._phrases), len(INTENTS))

        # ③ Warmup
        self.classify("teste de aquecimento")
        log.info("✓ IntentClassifier pronto — warmup concluído.")

    def classify(self, texto: str) -> tuple[str | None, float]:
        """Retorna (intent, score). (None, score) se abaixo do threshold."""
        texto_norm = normalize(texto)
        if not texto_norm:
            return None, 0.0

        query = self._model.encode(
            texto_norm, convert_to_tensor=True, show_progress_bar=False
        )
        scores = self._util.cos_sim(query, self._embeddings)[0]
        best_idx = int(scores.argmax())
        # ④ .item() obrigatório — tensor vs float lança RuntimeError
        best_score = float(scores[best_idx].item())
        best_intent = self._phrase_intents[best_idx]

        log.debug("Semântico: \"%s\" → %s (%.2f)", texto_norm, best_intent, best_score)

        if best_score >= self.threshold:
            return best_intent, best_score
        return None, best_score