FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./

COPY . .

RUN npm install

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["npx", "next", "dev", "-p", "3000"]