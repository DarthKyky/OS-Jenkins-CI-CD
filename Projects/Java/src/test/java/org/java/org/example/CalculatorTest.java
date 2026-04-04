package org.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class CalculatorTest {

    @Test
    void add_shouldReturnCorrectSum() {
        Calculator calculator = new Calculator();
        assertEquals(5, calculator.add(2, 3));
    }

    @Test
    void subtract_shouldReturnCorrectDifference() {
        Calculator calculator = new Calculator();
        assertEquals(3, calculator.subtract(5, 2));
    }

    @Test
    void multiply_shouldReturnCorrectProduct() {
        Calculator calculator = new Calculator();
        assertEquals(12, calculator.multiply(3, 4));
    }
}
