FROM node:22-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY app ./app
COPY next.config.mjs ./
ENV PYTHON_API_URL=http://api:8000
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
