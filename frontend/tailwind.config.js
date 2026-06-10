/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/renderer/**/*.{js,ts,jsx,tsx,html}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Figtree Variable', 'sans-serif'],
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
      colors: {
        // shadcn/ui 基础 token（必须用 CSS 变量，供 @apply border-border 等使用）
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: 'var(--card)',
        'card-foreground': 'var(--card-foreground)',
        popover: 'var(--popover)',
        'popover-foreground': 'var(--popover-foreground)',
        primary: 'var(--primary)',
        'primary-foreground': 'var(--primary-foreground)',
        secondary: 'var(--secondary)',
        'secondary-foreground': 'var(--secondary-foreground)',
        muted: 'var(--muted)',
        'muted-foreground': 'var(--muted-foreground)',
        accent: 'var(--accent)',
        'accent-foreground': 'var(--accent-foreground)',
        destructive: 'var(--destructive)',
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        sidebar: 'var(--sidebar)',
        'sidebar-foreground': 'var(--sidebar-foreground)',
        'sidebar-primary': 'var(--sidebar-primary)',
        'sidebar-primary-foreground': 'var(--sidebar-primary-foreground)',
        'sidebar-accent': 'var(--sidebar-accent)',
        'sidebar-accent-foreground': 'var(--sidebar-accent-foreground)',
        'sidebar-border': 'var(--sidebar-border)',
        'sidebar-ring': 'var(--sidebar-ring)',
        // 项目自定义品牌色（rgb 格式支持 opacity modifier）
        'accent-cyan': 'rgb(0 240 255 / <alpha-value>)',
        'accent-magenta': 'rgb(255 0 255 / <alpha-value>)',
        'accent-green': 'rgb(0 255 65 / <alpha-value>)',
        'team-red': 'rgb(255 68 68 / <alpha-value>)',
        'team-blue': 'rgb(68 136 255 / <alpha-value>)',
        'team-yellow': 'rgb(255 170 0 / <alpha-value>)',
      },
      // 新增阴影
      boxShadow: {
        'glow-cyan': 'var(--shadow-glow-cyan)',
        'glow-red': 'var(--shadow-glow-red)',
        'glow-blue': 'var(--shadow-glow-blue)',
        'glow-yellow': 'var(--shadow-glow-yellow)',
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
