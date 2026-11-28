# Demo persona

What the public guest account sees: a synthetic job search, rebuilt by `manage.py seed_demo`.

Every company is a well-known fictional name and every person is invented; the home location is
a public landmark. Nothing here may come from a real search (project rule 1). Dates are written
relative to the day of seeding (`-12d`, `+3d`), so the demo never goes stale.

The file is loaded through the same validation and importer as a user's own data, so a mistake
here fails `seed_demo` instead of producing a broken demo.
