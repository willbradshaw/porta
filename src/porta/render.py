"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator and the
debug-ascii rasterizer. SVG is built from stdlib string templating only (no
runtime dependencies).

Stage 0: placeholder. The ascii rasterizer lands in Stage 2, SVG in Stage 4.
"""
