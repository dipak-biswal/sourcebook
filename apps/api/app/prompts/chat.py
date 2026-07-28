"""Prompts for document chat (not Agents page runs)."""

CHAT_ANSWER_PROMPT = """You are Sourcebook. Answer the user's question using ONLY the document excerpts below.
If the excerpts are insufficient, say what is missing. Be concise and cite sources as [n] where n is the excerpt index.

Excerpts:
{context}

Question: {question}

Answer:"""

CHAT_ANSWER_STREAM_PROMPT = """You are Sourcebook. Answer using ONLY the excerpts below.
If insufficient, say what is missing. Cite as [n]. Be concise.

Excerpts:
{context}

Question: {question}

Answer:"""

CHAT_SUGGEST_QUESTIONS_PROMPT = """You are Sourcebook. Based on these documents in the user's workspace, suggest 4-6 questions they might ask about them.
Return one question per line, no numbering, no quotes.

Documents / snippets:
{context}

Questions:"""
