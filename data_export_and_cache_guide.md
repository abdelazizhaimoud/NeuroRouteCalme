# Data Export and Cache Guide

## Purpose
This document explains what the Casablanca pedestrian pipeline exports, why each format exists, and how to keep the outputs readable.

## What the pipeline builds
The script queries OpenStreetMap through OSMnx and builds a pedestrian graph for Casablanca.

- Nodes represent intersections or routing points.
- Edges represent walkable street segments.

This is the base spatial structure used by NeuroRoute Calme.

## Why GraphML
GraphML is the routing file.

- It preserves the full graph structure.
- It stores node and edge attributes.
- It loads directly back into NetworkX and OSMnx.
- It is the best format for shortest-path and weighted routing algorithms.

Use GraphML when you want to run routing logic, recompute paths, or reload the graph exactly as built.

## Why Nodes GeoJSON
Nodes GeoJSON is a readable spatial output for points.

- It is easy to inspect in GIS tools.
- It helps validate where intersections are located.
- It is useful for debugging coverage and topology.

Use Nodes GeoJSON for map inspection, QA, and point-based analysis.

## Why Edges GeoJSON
Edges GeoJSON is the key file for segment analysis.

- Each feature is one street segment.
- The geometry is a LineString.
- The properties hold road attributes such as highway, maxspeed, lanes, and length.

This is the file you enrich with calmness, crowd, and walkability features.

## Why GeoJSON exactly
GeoJSON is used because it is:

- open and widely supported
- readable in plain text
- compatible with Python, QGIS, web maps, and APIs
- geometry-native, so points and lines stay attached to their attributes

GeoJSON is not the most compact format, but it is one of the most practical for spatial debugging and interoperability.

## Why the cache is not meant to be read directly
OSMnx cache files are internal HTTP cache artifacts.

- They are optimized for reuse.
- They are hash-based, not human-friendly.
- They are not the right place to inspect project logic.

For readability, the project should expose:

- a run manifest JSON
- preview GeoJSON files
- preview CSV files

## Recommended folder structure

```text
outputs/casablanca_morocco/
  raw/
  preview/
  table/
  meta/

cache/
  osmnx_http/
```

## Practical rule
- GraphML is the source of truth for routing.
- Edges GeoJSON is the source of truth for segment enrichment.
- Preview files are for humans.
- Cache files are for speed, not reading.