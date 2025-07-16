# Legacy Files

This directory contains the original monolithic version of AudiobookMakerPy for reference purposes.

## Files

- **AudiobookMakerPy.py** - The original single-file implementation (v1.x)

## Important Notes

⚠️ **These files are for reference only and should not be used in production.**

The project has been refactored into a modern Python package structure. Please use the new package instead:

```bash
# Install the new package
pip install .

# Use the new CLI
audiobookmaker /path/to/files/
```

## Migration

If you were using the old script:

**Old usage:**
```bash
python AudiobookMakerPy.py /path/to/files/
```

**New usage:**
```bash
audiobookmaker /path/to/files/
```

For programmatic usage, see the [API documentation](../docs/API.md).

## Why This Was Moved

The original script was moved to maintain backward compatibility while encouraging adoption of the new, more maintainable structure. The new package provides:

- Better error handling
- Improved modularity
- Comprehensive testing
- Modern Python packaging
- Professional documentation
- Easier maintenance and contribution

## Cleanup

These legacy files may be removed in a future version once the transition is complete.