/// <reference types="cypress" />

describe('st.title', () => {
  beforeEach(() => {
    cy.visit('http://localhost:3000/')
  })

  it('displays a title', () => {
    cy.get('.element-container h1')
      .should('contain', 'Hello, Streamlit!')
  })
})
