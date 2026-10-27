/** Design tokens from DESIGN.md section 5 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#1D4ED8', dark: '#1E40AF' }, accent: '#F59E0B', success: '#16A34A', danger: '#DC2626',
        seat: { available: '#E2E8F0', selected: '#1D4ED8', held: '#F59E0B', booked: '#94A3B8' },
      },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
      borderRadius: { card: '12px' },
      boxShadow: { card: '0 18px 45px -28px rgba(15, 23, 42, 0.35)' },
    },
  },
  plugins: [],
}
