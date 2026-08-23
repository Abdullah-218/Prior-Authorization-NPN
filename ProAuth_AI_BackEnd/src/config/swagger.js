import swaggerJSDoc from 'swagger-jsdoc';

const options = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'PriorAuth AI API',
      version: '1.0.0',
      description: 'REST API for the Prior Authorization Automation Platform.',
    },
  },
  apis: ['./src/routes/*.js'],
};

export default swaggerJSDoc(options);
