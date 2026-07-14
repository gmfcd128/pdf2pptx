const StyleLintPlugin = require('stylelint-webpack-plugin')

module.exports = {
  publicPath: './',
  devServer: {
    port: 5173,
    proxy: {
      // Local non-Docker dev: `dotnet run` launches the backend on
      // http://localhost:8080 (see web/backend's launchSettings.json), so this
      // makes the browser see everything as same-origin here too, just like
      // the nginx reverse proxy does in the Docker/production path -- no CORS
      // configuration needed in either case.
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  css: {
    loaderOptions: {
      sass: {
        prependData: `
          @import "~@/assets/styles/variable.scss";
          @import "~@/assets/styles/mixin.scss";
        `,
      },
      less: {
        lessOptions: {
          modifyVars: {
            'primary-color': '#d14424',
            'text-color': '#41464b',
            'font-size-base': '13px',
            'border-radius-base': '2px',
          },
          javascriptEnabled: true,
        },
      },
    },
  },
  configureWebpack: {
    plugins: [
      new StyleLintPlugin({
        files: ['src/**/*.{vue,html,css,scss,sass,less}'],
        failOnError: false,
        cache: false,
        fix: false,
      }),
    ],
  },
}