# Multi-stage: node image builds the static bundle, nginx just serves it (and
# reverse-proxies /api to the backend container) -- no node runtime ships in the
# final image.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
# No package-lock.json is committed (nothing in this repo has run `npm install`
# to generate one yet) -- `npm install` resolves and writes it on first build;
# switch to `npm ci` once a lockfile exists and is committed, for reproducible
# builds.
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
