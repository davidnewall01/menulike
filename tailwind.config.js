/**
 * Tailwind CSS config — admin templates only.
 *
 * Rebuild after changing Tailwind classes in admin templates:
 *   tools/tailwindcss -i app/static/admin/input.css -o app/static/admin/admin.css --minify
 *
 * Watch mode (auto-rebuild on save):
 *   tools/tailwindcss -i app/static/admin/input.css -o app/static/admin/admin.css --watch
 *
 * The standalone CLI binary lives in tools/ (gitignored). Download from:
 *   https://github.com/tailwindlabs/tailwindcss/releases (tailwindcss-windows-x64.exe)
 *
 * The compiled admin.css IS committed — Railway serves it as a static file,
 * no build step in deploy.
 *
 * @type {import('tailwindcss').Config}
 */
module.exports = {
  content: [
    "./app/templates/admin/**/*.html",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
