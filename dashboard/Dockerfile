FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
# Ensure modern styling libraries are robustly injected
RUN npm install -D tailwindcss @tailwindcss/vite postcss autoprefixer
COPY . .
EXPOSE 5173
# Expose externally for Docker host routing
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
