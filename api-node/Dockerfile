FROM node:22-alpine

WORKDIR /code
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src

EXPOSE 8000
CMD ["node", "src/server.js"]
