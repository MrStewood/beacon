# Embedding Beacon

## JavaScript Widget

Add a live resource directory to any website:

```html
<script src="https://mrstewood.github.io/beacon/embed/widget.js"
        data-county="knox"
        data-need="food"
        data-theme="light"
        data-limit="10">
</script>
```

### Options

| Attribute | Values | Default | Description |
|-----------|--------|---------|-------------|
| `data-county` | County name | (all) | Filter by county |
| `data-need` | Need ID | (all) | Filter by need category |
| `data-theme` | `light`, `dark` | `light` | Color theme |
| `data-limit` | Number | `50` | Max results to show |

### Need IDs
`addiction`, `clothing`, `community`, `crisis`, `documents`, `education`, `family`, `food`, `health`, `housing`, `jobs`, `legal`, `mental-health`, `shelter`, `transportation`, `veterans`

### Example: Dark theme, food resources in Laurel County
```html
<script src="https://mrstewood.github.io/beacon/embed/widget.js"
        data-county="laurel"
        data-need="food"
        data-theme="dark"
        data-limit="10">
</script>
```

## Iframe Widget

For isolated styling (recommended for production):

```html
<iframe src="https://mrstewood.github.io/beacon/embed/widget.html?county=knox&need=food&theme=light&limit=10"
        style="width:100%;height:400px;border:none;border-radius:10px"
        title="Beacon Resource Directory">
</iframe>
```

### Iframe Parameters

Same as JavaScript widget attributes, passed as URL query parameters.

## Direct Data Access

Fetch data directly for custom implementations:

```javascript
const response = await fetch('https://mrstewood.github.io/beacon/data/resources.json');
const data = await response.json();
```

See [API.md](API.md) for full documentation.

## Styling

The widget uses minimal, self-contained CSS. It won't conflict with your site's styles.

### Theme Colors
- **Light**: White background, blue accents
- **Dark**: Dark background, light blue accents

## Accessibility

- Widget uses semantic HTML
- Links have `rel="noopener noreferrer"`
- All resource data is HTML-escaped
- Keyboard navigable

## Security

- All resource data is escaped before HTML insertion
- External links use `rel="noopener noreferrer"`
- No third-party scripts or tracking
- No user data collection

## Troubleshooting

**Widget not loading?**
1. Check browser console for errors
2. Verify the script URL is correct
3. Ensure your site allows loading external scripts

**No resources showing?**
1. Check `data-county` and `data-need` values are valid
2. Try without filters to see all resources
3. Verify the data URL is accessible
