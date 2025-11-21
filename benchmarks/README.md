# SUS Performance Benchmarking

This directory contains performance benchmarking tools for the SUS scraper.

## Quick Start

### Run pytest benchmarks
```bash
# Run all benchmarks
uv run pytest tests/test_performance.py --benchmark-only

# Save baseline
uv run pytest tests/test_performance.py --benchmark-only --benchmark-save=baseline

# Compare against baseline
uv run pytest tests/test_performance.py --benchmark-only --benchmark-compare=baseline
```

### Run standalone benchmark
```bash
# Benchmark 100 pages (default)
python benchmarks/benchmark_crawler.py

# Benchmark custom page count
python benchmarks/benchmark_crawler.py --pages 500
```

## Performance Targets

- **Throughput**: 15+ pages/sec (5x improvement from baseline)
- **Memory**: <500MB for 1000 pages
- **HTTP/2**: ~17% faster requests vs HTTP/1.1 (observed in tests/test_http2.py)
- **Connection pooling**: 60-80% connection overhead reduction (tests/test_connection_pooling.py)

## Benchmark Types

### 1. Throughput Benchmarks (`test_performance.py`)
- `test_crawler_throughput_10_pages`: Small site performance
- `test_crawler_throughput_100_pages`: Medium site performance
- Measures pages/second crawl rate

### 2. I/O Benchmarks
- `test_async_file_write_performance`: Async file I/O throughput
- Measures concurrent file write performance

### 3. Component Benchmarks
- `test_token_bucket_rate_limiter_performance`: Rate limiter overhead
- Measures rate limiter acquisition speed

### 4. End-to-End Benchmark (`benchmark_crawler.py`)
- Real-world scraping against httpbin.org
- Tracks memory usage, throughput, latency
- Compares against performance targets

## Interpreting Results

### Regression Detection
If benchmarks show >10% performance degradation:
1. Identify which component regressed
2. Profile the specific code path
3. Check for blocking I/O, excessive allocations
4. Compare against baseline commit

### Memory Issues
If memory usage exceeds targets:
1. Check for memory leaks (growing over time)
2. Profile with `memory_profiler`
3. Verify queue sizes are bounded
4. Check for circular references

## CI Integration

Benchmarks run automatically on:
- Pull requests (compare against main)
- Nightly builds (track trends)
- Release tags (validate targets)

See `.github/workflows/benchmarks.yml` for CI configuration.
