"""Offline evaluation harness for the Feishu agent's tool routing.

See ``run_eval.py`` for the runner and ``routing_cases.py`` for the labelled
dataset. The harness exercises the *real* routing pipeline
(``handle_incoming_text``) and records which tool it selected, so the accuracy
number reflects production behaviour rather than a re-implementation.
"""
