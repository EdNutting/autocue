# Understanding Exponents & Logarithms

## A Deep Dive into Powers, Roots, and Their Applications

Hey everyone, welcome back to Maths Explained.

Today we're going to tackle one of the most important topics in mathematics: exponents and logarithms. Don't worry if you've found these confusing before - by the end of this video, you'll have a solid understanding.

### What Are Exponents?

Let's start with the basics. When we write 2^3, we mean 2 multiplied by itself 3 times. So 2^3 = 8.

The number 2 is called the base, and the number 3 is the exponent or power.

Here are some examples:

- 10^2 = 100
- 10^3 = 1,000
- 10^6 = 1,000,000

Notice how each time we increase the exponent by 1, we multiply by 10 again.

### Negative & Fractional Exponents

What about negative exponents? Well, 10^-1 = 0.1 and 10^-2 = 0.01. The negative sign means "take the reciprocal" or divide 1 by the result.

Fractional exponents represent roots. So 9^0.5 equals the square root of 9, which is 3. Similarly, 8^0.33 is approximately the cube root of 8, which gives us 2.

### Scientific Notation

Scientists and engineers use exponents constantly. A wavelength of light might be 5.5 x 10^-7 metres, or about 550nm in everyday terms.

The speed of light is approximately 3 x 10^8 m/s - that's 300,000,000 metres per second!

Computer storage also uses powers of 2:

- 1KB = 1,024 bytes
- 1MB ~ 1,000,000 bytes
- 1GB ~ 1,000,000,000 bytes
- 1TB = 1,024GB

Modern processors run @ speeds like 3.5GHz or 4.05GHz - that's billions of cycles per second.

### Comparing Values with Inequalities

When working with exponents, we often need to compare values:

- If x > 1 and n > 0, then x^n > 1
- If 0 < x < 1 and n > 0, then x^n < 1
- For any x >= 1, we have x^2 >= x
- When x <= 0 and n is even, x^n >= 0

### The Logarithm: The Inverse Operation

Now for logarithms. If 10^2 = 100, then log base 10 of 100 = 2. The logarithm asks: "what power do I need?"

Common logarithms use base 10, written as log(x) or log10(x). Natural logarithms use base e ~ 2.718, written as ln(x).

The relationship is: if b^y = x, then log_b(x) = y

### Properties of Logarithms

Here are the key properties:

1. log(a x b) = log(a) + log(b)
2. log(a / b) = log(a) - log(b)
3. log(a^n) = n x log(a)

For example: log(1,000) = log(10^3) = 3

And: log(50) = log(100 / 2) = log(100) - log(2) = 2 - 0.301 ~ 1.699

### Real-World Applications

**Earthquake Magnitude:** The Richter scale is logarithmic. A magnitude 6 earthquake releases ~32 times more energy than a magnitude 5. A magnitude 8 is about 1,000 times stronger than a 6!

**Sound Intensity:** We measure sound in decibels (dB). Normal conversation is about 60dB, while a rock concert might hit 110dB - that's 100,000 times more intense!

**pH Scale:** Chemistry uses pH = -log[H+]. Pure water has pH = 7. A pH of 3 is 10,000 times more acidic than pH 7.

**Data Compression:** Algorithms use log_2 to measure information. With 8 bits, we can represent 2^8 = 256 different values.

### Computing Performance

Let's talk about algorithm complexity:

- O(1) - constant time
- O(log n) - logarithmic, very efficient
- O(n) - linear
- O(n^2) - quadratic, gets slow fast
- O(2^n) - exponential, becomes impractical

For n = 1,000,000:
- log(n) ~ 20 operations
- n = 1,000,000 operations
- n^2 = 1,000,000,000,000 operations

That's why choosing the right algorithm matters!

### Units & Measurements

Speaking of computing, here are some common measurements:

- Latency: 1ms to 100ms for network requests
- CPU frequency: 2.4GHz to 5.0GHz
- Memory bandwidth: 25GB/s to 100GB/s
- Storage speed: 500MB/s for SSDs, 100-200MB/s for HDDs

In physics:
- Room temperature: ~20C or ~68F
- Absolute zero: -273.15C or 0K
- Speed of sound: ~343m/s or ~767mph
- Distance to the moon: ~384,400km or ~238,855mi

### Practice Problems

Try these yourself:

1st problem: Calculate 2^10. The answer is 1,024.

2nd problem: What is log_2(256)? Since 2^8 = 256, the answer is 8.

3rd problem: Simplify 10^3 x 10^4. Answer: 10^7 = 10,000,000.

23rd problem in our series: If you have 50% annual growth, how many years to double? Using the rule of 72, it's approximately 72 / 50 ~ 1.44 years.

### Summary

Today we covered:

- Exponents: x^n means x multiplied by itself n times
- Negative exponents: x^-n = 1 / x^n
- Fractional exponents: x^0.5 = square root of x
- Logarithms: the inverse of exponentiation
- log(a x b) = log(a) + log(b)
- log(a / b) = log(a) - log(b)
- log(a^n) = n x log(a)

Thanks for watching! If this video helped you, please give it a thumbs up & consider subscribing. Drop a comment below if you have questions or want to see more topics like this.

See you in the next video!
