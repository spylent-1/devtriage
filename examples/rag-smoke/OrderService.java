package demo;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

// Synthetic diagnostic input; this directory is not a deployable application.
public class OrderService {
    private final DataSource pool;
    public OrderService(DataSource pool) { this.pool = pool; }
    public void checkout() throws SQLException {
        try (Connection connection = pool.getConnection()) {
            connection.createStatement().execute("SELECT 1");
        }
    }
}
