export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        legal: {
          900: '#0a1628',
          800: '#0f1f3d',
          700: '#152d5e',
          600: '#1a3a7f',
          500: '#1e4094',
          400: '#2d5cc5',
          300: '#4d7fe8',
          200: '#8aaff5',
          100: '#c5d9fa',
          50: '#e8f0fe',
        },
        accent: {
          gold: '#c9a84c',
          red: '#c0392b',
          green: '#27ae60',
        },
      },
      fontFamily: {
        serif: ['Noto Serif SC', 'STSong', 'SimSun', 'serif'],
      },
    },
  },
  plugins: [],
}
